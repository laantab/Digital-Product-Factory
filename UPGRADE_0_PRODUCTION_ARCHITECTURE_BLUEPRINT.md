# Upgrade 0 — Production Architecture Blueprint

Version 3 — revised 2026-09-14 after completing the §26 verification gate.
Documentation only. No code, dependency, Render, database, storage or
deployment change is authorised by this document.

**What changed in v3:** §26 verification is complete. Five facts verified,
three remain dashboard-only unknowns, and one verified finding is a
blocker that reorders the migration. Four changes applied throughout:
binary extraction now precedes the Postgres cutover; the worker is sized
`1c-2g`; a paid Postgres tier with recovery is now a requirement; and the
storage target is an external S3-compatible provider.

---

## 1. Executive summary

The Factory's product engines are good. Its execution plumbing is not.
Between v1.7.6 and v1.7.10, four separate production defects surfaced in
the ebook build, each invisible to a 2,800-test green gate, each fixed,
each followed by a new one. They were four symptoms of one root
condition: **multi-minute product generation runs inside a synchronous
HTTP request, in the same process that serves customers, against a single
JSON blob with no concurrency control.**

Upgrade 0 replaces that execution model and nothing else:

> **KEEP THE PRODUCTS. REPLACE THE PLUMBING.**

Target: the customer's browser starts a job and may close. A separate
background worker owns execution, claims work atomically from a durable
Postgres job table, checkpoints every bounded unit, survives its own
death and every deploy, and writes customer assets to shared object
storage the web service can serve. Product engines, QA, renderers,
covers, puzzles, planners, packaging, Function Lock, Command Center and
the test suite are preserved as-is.

Verification (§26) confirmed the shape of this design and surfaced one
blocker that changes its **order**: 64% of project rows currently embed
base64 PDFs in the database, the largest measured row being ~56 MB.
Binary extraction is therefore a migration **prerequisite**, not a later
optimisation.

Scope discipline: Upgrade 0 changes **how work is executed**, never
**what a product is supposed to be**.

---

## 2. Current architecture (verified in code and data, 2026-09-14)

| Layer | Today |
|---|---|
| Web | Flask 3.1.1, Gunicorn on Render. Start command is **dashboard-only, not in this repo**; timeout and worker count remain unverified |
| Instance | `0.5c-512mb` — 0.5 CPU, 512 MB RAM, $7/month (our deployment record, 2026-09-11) |
| Disk | 10 GB persistent disk at `/var/data`; `FACTORY_DB_PATH=/var/data/projects.db`, `FACTORY_EXPORTS_DIR=/var/data/exports` |
| Instancing | **Necessarily single-instance** — Render prohibits multi-instance scaling on a service with a disk attached |
| Deploys | **Not zero-downtime** — a disk forces stop-then-start, killing in-flight generation |
| Execution | Synchronous, inside the web request. `advance_build()` runs one stage per `/ebook/build/<id>/advance` POST |
| Trigger | The customer's **browser** drives the loop (`_ebookBuildLoop`, `static/js/app.js`) |
| State | SQLite (WAL), one table: `projects(id, name, type, data TEXT, user_saved, system_test, temporary, created_at, updated_at)` |
| Project state | The **entire** workspace — rail, chapters, ledger, QA findings, build state — is one JSON blob in `projects.data` |
| Writes | `database.update_project(pid, None, data)` **replaces the whole blob**; no version, no compare-and-swap |
| **Artifacts — two coexisting models** | **(a)** ebook → files on disk under `EXPORTS_DIR`, referenced by `package_id`. **(b)** other product types → **base64 PDF embedded in `projects.data`** (`pdf_bytes`), decoded at `services/packaging.py:533` |
| File writes | 30+ modules write directly to local `EXPORTS_DIR`; Flask serves downloads with `send_from_directory` off the same disk |
| Idempotency | Per-workspace dict inside the blob: `ebook_workspace.paid_call_ledger.idempotency_keys` |
| Queue/worker | **None.** `requirements.txt` contains no Celery, RQ, APScheduler or Redis |
| Providers | `services/ai_providers.py` — opt-in local Ollama, fail-closed to cloud (v1.7.8) |
| Protection | Function Lock registry: 4 LOCKED, 6 PROTECTED functions; Fast + Full gates |

### 2.1 Measured data (local, read-only, 2026-09-14)

| Measurement | Value |
|---|---|
| `projects.db` file | 177 MB (186,044,416 bytes) |
| Live blob bytes | 76.9 MB across **114 rows** |
| Rows embedding base64 PDFs (`pdf_bytes`) | **73 of 114 — 64%** |
| Largest single row | **~56 MB** (`pdf_bytes` 53.1 MB + `cover_design` 2.9 MB) |
| Still current? | Yes — present in rows updated 2026-09-09 → 09-11 |
| `exports/` | **1.9 GB across 838 package directories** |

Production equivalents are **unverified** — they live on Render's disk and
cannot be read from the development environment.

## 3. Root architectural problems

1. **Long work inside a request.** A book takes minutes; a web request may
   not. Gunicorn kills the worker mid-write (`handle_abort` → `sys.exit(1)`).
2. **The browser is the scheduler.** Close the tab and the build stops.
3. **Whole-blob read-modify-write.** `update_project` replaces all state.
   A stale in-memory copy silently erases newer work — this *already*
   caused v1.7.9's data loss **with one writer.** It becomes a structural
   lost-update hazard the moment a worker writes concurrently.
4. **Binary artifacts inside the state row.** 64% of rows carry base64
   PDFs; the largest is ~56 MB. Every checkpoint rewrites the entire row.
5. **Web and generation are operationally coupled.** A deploy, restart,
   OOM or traffic spike takes generation with it — and because a disk is
   attached, every deploy is a hard stop, not a rolling one.
6. **Private local disk as the asset store.** A disk cannot be shared
   between Render services, so no second process can produce or serve
   customer files.
7. **Failure state is implicit.** Retry/attempt/lease/error semantics are
   spread across an ad-hoc dict rather than a typed, queryable model.
8. **No production observability.** Diagnosis this sprint depended on the
   owner pasting screenshots of Render logs.

## 4. Systems to preserve (do not rewrite)

Ebook stage definitions and rail; `run_chapter_pipeline` and the chapter
contract/validator; accepted-chapter persistence semantics;
`execute_correct_manuscript` and manuscript QA; all cover systems and
final-cover QA authorities (Upgrade 1); Word Search / Crossword /
Coloring Book / Math Worksheet / Spelling Worksheet engines; Planner
theme + design-rating system; `services/packaging.py` PDF/ZIP export;
Editor-in-Chief QA; artifact DRAFT/APPROVED/LOCKED lifecycle; Factory
Market Advantage; invite gate; Function Lock registry and enforcement;
Command Center; the entire acceptance test suite.

**These are the products. They are not in scope for redesign.**

## 5. Systems to replace or deprecate

| Replace | With |
|---|---|
| Browser-driven `_ebookBuildLoop` as the *driver* | Worker owns execution; browser polls read-only status |
| Whole-blob `update_project` as the only write path | Typed job/stage rows + optimistic concurrency on the blob |
| **Base64 binaries inside `projects.data`** | **Object-storage keys + `assets` rows** |
| SQLite in **production** | PostgreSQL, paid tier (SQLite stays valid for tests) |
| Direct `EXPORTS_DIR` filesystem coupling | Storage abstraction over shared object storage |
| Implicit attempts/ceiling in `ebook_build` dict | `jobs` table: status, attempt, lease, next_retry_at |
| Ad-hoc `log.error` only | Structured job events + queryable history |

Deprecated but **retained**: the `/advance` endpoint stays as an
idempotent manual nudge and fallback. It is never the primary driver again.

## 6. Proposed target architecture

```
CUSTOMER (browser — may close at any time)
   │  POST /ebook/build              → returns {project_id, job_id}
   │  GET  /ebook/build/<id>/status  (read-only, fast, no work)
   ▼
FLASK WEB SERVICE  ── invite gate, projects, enqueue, status,
   │                  preview, approve, download.  NO generation.
   ▼
POSTGRESQL (durable shared state — paid tier, PITR)
   │   projects · jobs · work_units · job_events · assets
   ▼
JOB MANAGER  (thin module: enqueue / claim / heartbeat / complete / fail)
   │   atomic claim via SELECT … FOR UPDATE SKIP LOCKED + lease
   ▼
BACKGROUND WORKER (separate Render service, 1c-2g, N=1 to start)
   │   loop: claim → run ONE bounded unit → checkpoint → heartbeat → repeat
   ▼
EXISTING PRODUCT ENGINES / AI PROVIDERS      ← unchanged
   ▼
PRODUCT-SPECIFIC QA (Upgrade 1 authorities)  ← unchanged
   ▼
EXTERNAL S3-COMPATIBLE OBJECT STORAGE
   │   covers · images · PDFs · ZIPs · previews
   │   DB stores keys + metadata; storage holds bytes
   ▼
CUSTOMER DOWNLOAD  ·  (future) PIN FACTORY PRO
```

The web service and the worker share **only** Postgres and object
storage. Neither can kill the other. Verified constraint driving this:
a Render persistent disk is accessible by **one service instance only**
and cannot be reached from any other service — so shared object storage
is mandatory, not preferable.

## 7. Durable job-state model

Two levels, deliberately:

**Job** — one customer-visible piece of work (`BUILD_EBOOK`). Owns status,
attempts, lease, retry schedule, customer-safe message.

**Work unit** — one bounded, individually-idempotent step inside a job
(`stage:manuscript:chapter:7`). This is v1.7.10's concept, promoted to a
first-class, durable row.

```
QUEUED ──claim──► CLAIMED ──start──► RUNNING ──unit done──┐
   ▲                                    │                 │ (more units)
   │                                    │                 └──► RUNNING
   │              lease expired ────────┘
   │                                    │
   ├──◄─ WAITING_RETRY ◄── retryable failure (backoff, attempt+1)
   │                                    │
   │                                    ├──► SUCCEEDED
   │                                    ├──► FAILED_FINAL (attempts exhausted)
   └──────────────────────────────────  └──► BLOCKED (needs a human decision)
```

Crash recovery is a database fact, not a code path: a worker that dies
stops heartbeating; its lease expires; a sweeper returns the job to
`QUEUED`; a worker re-claims it and resumes from the last completed work
unit. Deploys are the same event as a crash and are handled identically —
which matters more than it first appears, because the current disk-bound
service has **no zero-downtime deploys** at all.

## 8. Persistence model

### 8.1 Two prerequisites, both before any worker writes

**(a) Optimistic concurrency.** `projects.data` holds all state and
`update_project()` replaces it wholesale. Introducing a second writer
without fixing this would manufacture data loss. Add
`projects.version BIGINT`; every write becomes
`UPDATE … SET data=?, version=version+1 WHERE id=? AND version=?`.
Zero rows updated ⇒ someone else wrote ⇒ re-read, re-apply, retry. This
also closes the *existing* single-writer hazard, so it is worth landing
on SQLite immediately, before any infrastructure change.

**(b) Binary extraction — newly identified, and a blocker.** 73 of 114
rows embed base64 PDFs; the largest row is ~56 MB. Every
`update_project()` on such a row rewrites tens of megabytes. Under the
worker's per-unit checkpointing that becomes, on Postgres, TOAST churn
plus WAL amplification on *every chapter*, inflating backups and
replication for no benefit. **Binaries must move to object storage before
the Postgres cutover, not after it.** See §24.

This answers the design question directly: storing large file blobs in
the database is not merely un-preferable — it is already causing measurable
harm in the current system.

### 8.2 Recommended schema (Postgres)

```sql
-- EXISTING, minimally extended -------------------------------------
ALTER TABLE projects ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
-- projects.data retains workspace state ONLY; no pdf_bytes, no base64
-- images. Binary artifacts live in object storage, referenced via assets.

-- JOBS --------------------------------------------------------------
CREATE TABLE jobs (
  job_id                UUID PRIMARY KEY,
  project_id            BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  product_type          TEXT   NOT NULL,          -- 'ebook', 'word_search', …
  job_type              TEXT   NOT NULL,          -- 'BUILD_PRODUCT', later 'CREATE_MARKETING_ASSETS'
  stage                 TEXT,                     -- current stage, e.g. 'manuscript'
  status                TEXT   NOT NULL,          -- QUEUED|CLAIMED|RUNNING|WAITING_RETRY|BLOCKED|SUCCEEDED|FAILED_FINAL|CANCELLED
  progress_percent      SMALLINT NOT NULL DEFAULT 0,
  attempt               INT    NOT NULL DEFAULT 0,
  max_attempts          INT    NOT NULL DEFAULT 5,
  priority              SMALLINT NOT NULL DEFAULT 100,
  provider              TEXT,
  idempotency_key       TEXT   NOT NULL,
  claimed_by            TEXT,
  lease_expires_at      TIMESTAMPTZ,
  heartbeat_at          TIMESTAMPTZ,
  available_at          TIMESTAMPTZ NOT NULL DEFAULT now(),  -- = next_retry_at when backing off
  started_at            TIMESTAMPTZ,
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at          TIMESTAMPTZ,
  error_code            TEXT,
  internal_error_detail TEXT,                     -- never rendered to a customer
  customer_safe_message TEXT,                     -- the only text the UI may show
  cost_estimated_usd    NUMERIC(10,4) NOT NULL DEFAULT 0,
  cost_spent_usd        NUMERIC(10,4) NOT NULL DEFAULT 0,
  billable_calls        INT    NOT NULL DEFAULT 0,
  payload               JSONB  NOT NULL DEFAULT '{}'::jsonb,
  result                JSONB  NOT NULL DEFAULT '{}'::jsonb,
  version               BIGINT NOT NULL DEFAULT 0,
  CONSTRAINT jobs_idem_unique UNIQUE (idempotency_key)
);
CREATE INDEX jobs_claimable_idx ON jobs (status, available_at, priority DESC);
CREATE INDEX jobs_project_idx   ON jobs (project_id, status);
CREATE INDEX jobs_lease_idx     ON jobs (status, lease_expires_at);

-- WORK UNITS (bounded, individually idempotent steps) ----------------
CREATE TABLE work_units (
  work_unit_id   UUID PRIMARY KEY,
  job_id         UUID NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
  unit_key       TEXT NOT NULL,   -- 'stage:manuscript:chapter:7:<contract_digest>'
  stage          TEXT NOT NULL,
  status         TEXT NOT NULL,   -- PENDING|RUNNING|SUCCEEDED|FAILED
  attempt        INT  NOT NULL DEFAULT 0,
  provider       TEXT,
  billable_calls INT  NOT NULL DEFAULT 0,
  cost_usd       NUMERIC(10,4) NOT NULL DEFAULT 0,
  result_ref     JSONB NOT NULL DEFAULT '{}'::jsonb,  -- asset keys / digests, never blobs
  started_at     TIMESTAMPTZ,
  completed_at   TIMESTAMPTZ,
  CONSTRAINT work_units_unique UNIQUE (job_id, unit_key)   -- ← the idempotency guarantee
);

-- EVENTS (append-only; observability + forensics) --------------------
CREATE TABLE job_events (
  event_id   BIGSERIAL PRIMARY KEY,
  job_id     UUID NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
  at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  kind       TEXT NOT NULL,    -- CLAIMED|UNIT_DONE|RETRY|LEASE_EXPIRED|QA_FAIL|CORRECTED|SUCCEEDED|FAILED
  stage      TEXT,
  worker_id  TEXT,
  detail     JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX job_events_job_idx ON job_events (job_id, at DESC);

-- ASSETS (shared storage metadata; bytes live in object storage) -----
CREATE TABLE assets (
  asset_id     UUID PRIMARY KEY,
  project_id   BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL,   -- cover|interior_image|pdf|zip|preview|marketing_image
  storage_key  TEXT NOT NULL UNIQUE,   -- 'projects/1234/exports/pkg-abc/ebook.pdf'
  content_hash TEXT NOT NULL,
  byte_size    BIGINT NOT NULL,
  mime_type    TEXT NOT NULL,
  approved     BOOLEAN NOT NULL DEFAULT FALSE,
  supersedes   UUID REFERENCES assets(asset_id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX assets_project_kind_idx ON assets (project_id, kind, approved);
```

`assets` is deliberately the exact shape Pin Factory Pro will later read:
approved assets, by project, by kind, by key. It is also the destination
for the 73 rows of embedded `pdf_bytes`.

## 9. Background-worker design

A single Python process, same repository, same product code:

```python
while not shutting_down:
    job = claim_one_job(worker_id)              # atomic; see §10
    if not job:
        sleep(poll_interval); continue
    try:
        with heartbeat(job):                    # renews lease while working
            unit = next_pending_unit(job)       # e.g. chapter 7
            if unit is None:
                finalize(job); continue
            run_one_unit(job, unit)             # existing engines, unchanged
            checkpoint(job, unit)               # durable, atomic, idempotent
    except Retryable as e:
        release_for_retry(job, e, backoff)      # attempt+1, available_at=now()+backoff
    except Fatal as e:
        fail_final(job, e)                      # customer_safe_message set
```

Non-negotiables:
- **One bounded unit per loop turn** — v1.7.10's rule, preserved.
- **Checkpoint before anything else.** A unit's result is durable before
  the loop advances.
- **Graceful shutdown** on SIGTERM: finish the current unit, release the
  lease, exit.
- **Never mutate an approved artifact.**
- **Worker concurrency starts at 1.** `SKIP LOCKED` makes N>1 correct
  whenever it is needed, without redesign.

Sizing: **`1c-2g` (1 CPU, 2 GB)**, not the web tier's `0.5c-512mb`. The
generation stack — PyMuPDF, Pillow, reportlab, xhtml2pdf rasterisation —
is memory-hungry, and 512 MB is too tight for it to be the process that
must not die.

## 10. Durable queue / backend choice

**Recommendation: PostgreSQL as the queue. No Redis, no Celery, not yet.**

```sql
UPDATE jobs SET status='CLAIMED', claimed_by=:worker, attempt=attempt+1,
       lease_expires_at=now() + interval '120 seconds',
       heartbeat_at=now(), started_at=COALESCE(started_at, now()),
       updated_at=now()
WHERE job_id = (
  SELECT job_id FROM jobs
   WHERE status IN ('QUEUED','WAITING_RETRY')
     AND available_at <= now()
   ORDER BY priority DESC, available_at ASC
   FOR UPDATE SKIP LOCKED
   LIMIT 1
)
RETURNING *;
```

Lease reclaim (a dead worker's job returns to the pool automatically):

```sql
UPDATE jobs SET status='QUEUED', claimed_by=NULL, lease_expires_at=NULL
WHERE status IN ('CLAIMED','RUNNING') AND lease_expires_at < now();
```

Why sufficient here: Factory volume is low, jobs are minutes long, and
`FOR UPDATE SKIP LOCKED` is a mature Postgres primitive. Adding Redis +
Celery now would add a broker to operate and a second source of truth
that can disagree with the database, for throughput the Factory does not
need.

**Adopt Redis/RQ/Celery only when a concrete trigger is hit:** sustained
queue depth one or two workers cannot drain; sub-second dispatch latency;
fan-out/chord workflows; scheduled/recurring jobs beyond a simple
sweeper; or job rates high enough that polling measurably loads Postgres.
None hold today.

## 11. Provider / configuration design

- **Fail closed.** Missing/unknown configuration selects the safe cloud
  provider, never a local one. Local generation is explicit opt-in
  (`FACTORY_AI_POLICY=local_first|local_only`), Ollama local-only.
- **Never infer the environment.** No platform-detection heuristics; two
  independent attempts at that failed in production this sprint.
- **Per-domain credentials, per-domain failure.** Product generation,
  Pinterest/Pin Factory and each future channel share no client or
  failure mode.
- **The worker is a configuration consumer, not a special case.** Both
  processes read one config module; provider keys
  (`AI_INTEGRATIONS_OPENAI_API_KEY`, `OPENAI_API_KEY`, `PEXELS_API_KEY`,
  `TAVILY_API_KEY`, `FACTORY_AI_POLICY`) must be present on **both**
  services. `PORT` and `FACTORY_INVITE_CODE` are web-only. `USERPROFILE`
  is Windows-only and must never be required on Render.

## 12. Startup health validation

Both processes validate before accepting work and log one structured
readiness line:

| Check | Web | Worker | On failure |
|---|---|---|---|
| Postgres reachable, migrations current | ✔ | ✔ | refuse to start |
| Object storage reachable, write+read+delete probe | ✔ | ✔ | refuse to start |
| Cloud AI provider key present and non-placeholder | ✔ | ✔ | refuse to start |
| `FACTORY_AI_POLICY` resolves to an explicit valid value | ✔ | ✔ | log it; local-only ⇒ refuse in production |
| Fonts/renderer assets materialised (`services/fonts/`) | — | ✔ | refuse to start |
| Disk/tmp writable | ✔ | ✔ | refuse to start |

A worker that cannot do its job must fail loudly at boot, not silently
per job — the failure mode that cost this sprint four rounds.

## 13. Error / recovery model

| Class | Example | Handling |
|---|---|---|
| Transient | provider 5xx/timeout, network reset | retry, exponential backoff + jitter, attempt+1 |
| Capacity | rate limit, budget ceiling near | longer backoff; `BLOCKED` if budget genuinely exhausted |
| Content/QA | manuscript fails structural QA | existing `execute_correct_manuscript`, re-QA, then approve or `BLOCKED` |
| Configuration | missing key, bad policy | `FAILED_FINAL` fast and loud |
| Poison | same unit fails deterministically at max attempts | `FAILED_FINAL`; prior completed units retained |
| Infrastructure | worker killed, deploy | lease expiry → automatic reclaim → resume |

Invariants, each violated at least once this sprint:
1. Recording a failure may only **add** information — never overwrite
   newer state (v1.7.9).
2. A completed work unit is never re-executed or re-billed (v1.7.10).
3. The customer sees only `customer_safe_message`.
4. A recoverable failure never becomes a customer-facing dead end (v1.7.6).

## 14. Logging / observability model

- **Structured JSON logs**, every line carrying `job_id`, `project_id`,
  `stage`, `attempt`, `worker_id`.
- **`job_events`** as the durable, queryable narrative of every job —
  diagnosis stops depending on scrollback screenshots.
- **Command Center panel**: active jobs, stage, attempt, lease age, last
  error code, oldest queued job, failed-final in 24h, spend per job.
- **Heartbeat/lease age** is the best liveness signal.
- **Secrets never logged.**

## 15. Render production topology

```
┌──────────────────────┐        ┌──────────────────────────┐
│  Web Service         │        │  Background Worker       │
│  0.5c-512mb (today)  │        │  1c-2g                   │
│  Flask + Gunicorn    │        │  python -m worker        │
│  customer traffic    │        │  generation · QA · export│
│  NO generation       │        │  concurrency 1 → N       │
└─────────┬────────────┘        └───────────┬──────────────┘
          │        both read/write          │
          ├─────────────┬───────────────────┤
          ▼             ▼                   ▼
   ┌─────────────────────────┐   ┌────────────────────────┐
   │ Render PostgreSQL       │   │ External S3-compatible │
   │ PAID tier (PITR)        │   │ object storage         │
   │ projects · jobs         │   │ covers · images · PDFs │
   │ work_units · job_events │   │ ZIPs · previews        │
   │ assets (metadata)       │   │ (bytes)                │
   └─────────────────────────┘   └────────────────────────┘
```

**Verified platform constraints shaping this topology:**

- A Render persistent disk *"is accessible by only a single service
  instance… You can't access a service's disk from any other service."*
  Shared object storage is therefore **mandatory** for a two-service
  design — there is no disk-sharing alternative.
- *"You can't scale a service to multiple instances if it has a disk
  attached."* The current web service has a 10 GB disk, so it is
  **single-instance today, necessarily**.
- *"Adding a disk to a service prevents zero-downtime deploys."* Every
  current deploy stops the instance before starting the new one — which
  is precisely why in-flight generation dies on deploy today.

Consequences: the web service streams downloads from object storage (or
issues short-lived signed URLs) instead of `send_from_directory`. Once
state and artifacts have moved, the disk is no longer the system of
record and may be reduced or removed — which would also restore
zero-downtime deploys and the option to scale the web tier.

## 16. Windows local development topology

Same shape, one machine, so local development cannot hide production
defects:

```
Launcher (one .bat)
 ├─ process 1: Flask web        (port 5055 owner / 5077 Claude)
 └─ process 2: python -m worker    ← same worker code as production
        ▼                ▼
   PostgreSQL (local)   local storage driver behind the same interface
                        (filesystem or MinIO/localstack), same API
```

**Recommendation: run PostgreSQL locally too.** `FOR UPDATE SKIP LOCKED`
has no SQLite equivalent, so a SQLite local path would need a *different*
claim implementation — exactly the "local hides production defects" trap.
Same engine both sides keeps job semantics identical.

- SQLite **remains** the test-suite engine (fast, isolated), with a
  stubbed job store or single-threaded claim shim, plus a contract test
  asserting both implementations obey the same claim/lease semantics.
- The local storage driver implements the same interface as the
  production S3 driver, so no call site differs between environments.
- Ollama stays an explicit local-only provider option, unchanged.
- If installing Postgres locally proves unacceptable, the fallback is
  SQLite + a single-worker advisory-lock shim, documented as a known
  divergence with the claim path excluded from local proof. Second-best,
  and a deliberate choice rather than a default.

## 17. Ebook pilot migration

Ebook is the only multi-minute build and therefore the only pilot.

1. **Preserve the current path.** v1.7.10 stays live and untouched while
   the new path is built behind `FACTORY_EXECUTION_MODE=legacy|worker`.
2. **Enqueue instead of execute.** `POST /ebook/build` creates the project
   *and* a `jobs` row, then returns immediately. In `legacy` mode the
   browser loop still drives; in `worker` mode it becomes read-only polling.
3. **Map stages to work units.** Existing `STAGES` become job stages;
   manuscript chapters become `work_units`. `stage_is_validated()` remains
   the completion authority — the worker asks exactly the question the
   orchestrator asks today.
4. **Adopt storage keys.** Ebook asset writes move behind the storage
   interface; `assets` rows record what exists.
5. **Cut over, one customer path, behind the flag.**

## 18. Migration plan for remaining products

Word Search, Crossword, Coloring Book, Math Worksheet, Spelling Worksheet
and Planners are fast, single-request generations with **no observed
timeout failures**. They are not migrated to worker execution for purity.

They are, however, affected by binary extraction: these are precisely the
product types whose rows carry embedded `pdf_bytes`. They must therefore:
- adopt the storage interface instead of DB-embedded binaries and direct
  `EXPORTS_DIR` writes;
- use optimistic-concurrency writes to `projects`;
- read provider configuration from the shared config module.

Any product that later grows a multi-minute path adopts the job/worker
model at that point — the hook exists, the work is not done speculatively.

## 19. Testing and production-release gates

Preserved: Fast Stability Gate, Full Release Gate, acceptance manifest,
`PROTECTED_GENERATOR_RULE.md` discipline, customer-path proof.

Added for Upgrade 0:
- **Job-contract tests** — claim is atomic under concurrency; an expired
  lease is reclaimed exactly once; a completed unit is never re-run;
  retry backoff respects `max_attempts`.
- **Crash-recovery tests** — kill a worker mid-unit; assert resume from
  checkpoint with no duplicate billable call.
- **Deploy-simulation test** — SIGTERM mid-job; assert clean release/resume.
- **Lost-update test** — concurrent web + worker writes; assert optimistic
  concurrency rejects the stale write instead of erasing data.
- **Binary-extraction tests** — a migrated project's PDF/ZIP downloads
  byte-identically from object storage; no row retains `pdf_bytes`.
- **Browser-close test** — start a job, drop the client, assert completion.
- **Storage-driver contract test** — local and S3 drivers behave identically.
- **No new flaky timing tests.** The worker loop exposes an injectable
  `tick()`; the suite never sleeps on real threads.

Unchanged rule: **a green gate is necessary, never sufficient.** Live
proof closes a production defect.

## 20. Function Lock 2.0 implications

1. **New shared dependencies to declare** — `services/jobs/*`,
   `services/storage/*`, the worker entrypoint, and (if touched) `app.py`
   and `database.py`. `invite_protection` (LOCKED) declares all of
   `app.py`, so enqueue-endpoint edits require its unlock/relock cycle.
2. **Binary extraction touches every product that embeds `pdf_bytes`** —
   including LOCKED functions (Word Search, Crossword, Coloring Book).
   Each unlocks, changes, re-proves and re-locks individually.
3. **Execution-mode dimension.** A function proven under `legacy` is not
   automatically proven under `worker`. Add an execution-mode field to a
   function's lock record.
4. **Re-lock requires live proof.** For ebook, the three-live-build gate
   (§24, 0D) is the proof — protected tests green is not enough.
5. **No bulk unlocking.**

## 21. Cost implications

### VERIFIED

| Fact | Value | Source |
|---|---|---|
| Current web service plan | `0.5c-512mb` — 0.5 CPU / 512 MB, **$7/month** | Our deployment record, `handoff_status.json:118` (2026-09-11) |
| Background workers have **no free tier** | Confirmed | Render Compute Plans docs |
| Worker plan lineup identical to web services | Confirmed | Render Compute Plans docs |
| Free Postgres has **no backups and no recovery** | *"Render does not provide recovery capabilities for databases on the Free compute plan"* | Render Postgres Backups docs |
| Paid Postgres recovery windows | Hobby = 3-day PITR; Pro or higher = 7-day PITR | Render Postgres Backups docs |

### UNKNOWN — must be read from the dashboard before committing

| Unknown | Why it matters |
|---|---|
| Price of a `1c-2g` background worker | Largest single new line item |
| Render Postgres tier prices | Paid tier is now a requirement, not an option |
| Postgres connection limits and included storage | Sizing and pooling decisions |
| Object-storage provider, region, egress terms | Provider not yet chosen |
| **Production** data volume (DB size, `exports/` size) | Storage cost and migration duration |

### Planning estimate — explicitly unverified

Required additions: one `1c-2g` worker (**> $7**, since it is a larger
plan than the current `0.5c-512mb`) + a paid Postgres tier + usage-priced
object storage. A prior estimate of roughly **$13–28/month** was based on
memory of pricing and is **not verified**; treat it only as an order of
magnitude until the dashboard figures are read. Partially offset if the
10 GB disk is reduced once it stops being the system of record.

Optional future scaling: additional workers, larger Postgres, a broker if
§10's triggers are ever hit, CDN for downloads.

The framing: this is a small monthly sum against a product line whose
builds currently die mid-run — but it is not a licence to over-provision.
One worker, the smallest Postgres tier that has recovery, and
usage-priced storage is the whole recommendation.

## 22. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | **Binary blobs in `projects.data`** — 73/114 rows, largest ~56 MB | **High** | Extract to object storage **before** the Postgres cutover (§24); verified blocker, not a theory |
| 2 | **Lost updates** from whole-blob writes with two writers | **High** | Optimistic concurrency lands first, on SQLite, before any infra change |
| 3 | **Storage blast radius** — 30+ modules write `EXPORTS_DIR` | **High** | Storage *interface* preserving current call semantics; ebook first |
| 4 | Dashboard-only unknowns (start command, prices, limits, prod volume) | Medium | Read before the cost commitment; none block the design |
| 5 | SQLite → Postgres migration of live customer projects | High | Side-by-side, read-only export/verify/import; rows already shrunk by binary extraction |
| 6 | Two deployables drift out of sync | Medium | Same repo, same image, deploy together; version stamped in readiness log |
| 7 | Duplicate paid generation during reclaim | Medium | `work_units` unique key; test asserts no re-billing |
| 8 | Long unit exceeds lease and is stolen mid-work | Medium | Heartbeat renews lease; lease ≫ p99 unit duration; fencing on `claimed_by` |
| 9 | Worker OOM on a 512 MB-class plan | Medium | Sized `1c-2g` for exactly this reason |
| 10 | Scope creep — "redesign everything" | Medium | §4 preserve-list is binding; ebook-only pilot |
| 11 | Postgres becomes a single point of failure | Medium | Paid tier with PITR; health check; loud failure |

## 23. Rollback strategy

Rollback is a **configuration change, not a code revert**, at every phase:

- `FACTORY_EXECUTION_MODE=legacy` restores the proven v1.7.10 path
  instantly. The legacy path is never deleted during migration.
- `/advance` is retained permanently as an idempotent nudge.
- **Binary extraction is dual-read.** During and after migration, the
  download path reads from object storage and falls back to the legacy
  source (`pdf_bytes` or `EXPORTS_DIR`) if a key is missing. Rows are not
  stripped of `pdf_bytes` until object-storage reads are proven, so
  rollback needs no data restore.
- Postgres migration is **additive-only** (new tables; `projects.version`
  defaults to 0). No destructive migration.
- Worker rollback = scale the worker service to zero; web unaffected.
- A tagged release + verified DB backup precedes every phase cutover.

## 24. Estimated implementation phases

**Revised order — binary extraction now precedes the Postgres cutover.**

| Phase | Content | Exit criterion |
|---|---|---|
| **0A** | This blueprint, approved | Owner approval |
| **0B-1** | Platform verification (§26) | **Complete** — 5 verified, 3 dashboard-only unknowns remain |
| **0B-2** | `projects.version` + optimistic concurrency, **on the existing SQLite DB**. No new infrastructure. Closes the existing single-writer hazard immediately | Lost-update test green; live behaviour unchanged |
| **0B-3** | **Storage interface + external S3-compatible driver + binary extraction.** Move `pdf_bytes` and `EXPORTS_DIR` artifacts to object storage; populate `assets`; dual-read with legacy fallback | Downloads byte-identical; no row retains `pdf_bytes`; storage contract test green |
| **0B-4** | **Postgres cutover** — now moving small rows, not 56 MB ones. Side-by-side export/verify/import | Data verified row-for-row; app runs on Postgres; legacy path still available |
| **0B-5** | Job manager + worker skeleton behind `FACTORY_EXECUTION_MODE`, off by default | Claim/lease/retry/crash/deploy tests green |
| **0C** | Ebook migrated to worker execution | Full Gate green; flag on in production |
| **0D** | **Three successful live ebook builds in a row**, different subjects, collectively covering manuscript, checkpointing, automatic correction, visuals, cover, design, QA, export, and browser-close/reopen | 3/3, no code change between |
| **0E** | Remaining long-running workflows; other products adopt storage/config/concurrency rules (they are the `pdf_bytes` carriers) | Per-product proof |

Rationale for the reorder: moving 56 MB rows into Postgres and *then*
letting a worker checkpoint against them would create TOAST and WAL churn
on every chapter, inflating backups and replication from day one.
Shrinking the rows first makes the Postgres cutover smaller, faster and
cheaper.

## 25. Recommended technology choices

| Concern | Choice | Why |
|---|---|---|
| Database | **PostgreSQL, paid tier (Hobby minimum)** | `SKIP LOCKED`, real transactions; **free tier has no backups or recovery and is disqualified as the customer system of record** |
| DB driver | `psycopg` (v3) | Current, well-supported |
| Schema changes | Plain SQL migration files applied at boot, verified by health check | Small, auditable |
| ORM | **None** — keep the existing thin DAL | `database.py` is already hand-rolled; SQLAlchemy is scope creep |
| Queue | **Postgres job table** (§10) | Sufficient; one fewer moving part |
| Worker | Plain Python process, same repo, **`1c-2g`** | No framework needed; 512 MB is too tight for the render stack |
| Object storage | **External S3-compatible provider** — Cloudflare R2, Backblaze B2 or AWS S3; **exact provider decision deliberately left open** | Render's own object storage is **alpha** and unsuitable for customer artifacts; a self-hosted MinIO on Render would be disk-bound to a single service, reintroducing the exact constraint being removed |
| Storage SDK | `boto3` (S3 API) | Portable across all three candidates |
| Local DB | PostgreSQL (same engine) | Keeps job semantics identical (§16) |
| Test DB | SQLite + claim shim + contract test | Keeps the suite fast and hermetic |
| Logging | stdlib `logging` + JSON formatter | No new dependency |
| Scheduling/sweeper | Worker's own loop | No APScheduler/cron needed |

Rejected for now, with the trigger that would change the answer:
Celery/RQ (§10 triggers), Redis (same), Render first-party object storage
(revisit when out of alpha), MinIO-on-Render (only if it can be reached by
both services, which a disk cannot), SQLAlchemy (only if the DAL becomes
unmanageable).

## 26. Verification gate — COMPLETE (2026-09-14)

Read-only verification. No code, schema, Render setting, environment
variable, branch, deployment, storage or customer project was modified;
no provider calls were made.

| # | Question | Answer | Result |
|---|---|---|---|
| 1 | Can a Render persistent disk attach to two services at once? | **No.** *"A persistent disk is accessible by only a single service instance… You can't access a service's disk from any other service."* Also: *"You can't scale a service to multiple instances if it has a disk attached"* and *"Adding a disk to a service prevents zero-downtime deploys."* | **VERIFIED** |
| 2 | Actual Render start command, Gunicorn `--timeout`, worker count? | Unknown. No Gunicorn configuration exists anywhere in this repository (no Procfile, absent from `requirements.txt`); the start command lives only in the Render dashboard. | **NOT VERIFIED** |
| 3 | Background Worker availability and price? | Available and suitable: *"run continuously… but they don't receive any incoming network traffic."* Identical plan lineup to web services, **minus the free tier**. Price not obtainable from documentation. | **VERIFIED** (availability) / **NOT VERIFIED** (price) |
| 4 | Postgres tiers, price, backups, connection limits? | *"Render does not provide recovery capabilities for databases on the Free compute plan"*; no logical backups either. Paid: Hobby = 3-day PITR, Pro or higher = 7-day PITR. Prices, connection limits and included storage not obtainable from documentation. | **VERIFIED** (backups) / **NOT VERIFIED** (price, limits) |
| 5 | Current instance size; does a worker fit beside it? | `0.5c-512mb` — 0.5 CPU / 512 MB, $7/month (`handoff_status.json:118`, `SESSION_HANDOFF_2026-09-11.md:141`). Too small for the generation stack ⇒ worker sized `1c-2g`. | **VERIFIED** (from our records, not a live dashboard read) |
| 6 | Single- or multi-instance web service today? | **Necessarily single-instance.** A 10 GB disk is mounted at `/var/data`, and Render prohibits multi-instance scaling with a disk attached. | **VERIFIED** (by derivation) |
| 7 | Object-storage provider, region, egress? | Render's own object storage is **alpha** — unsuitable for customer artifacts. MinIO-on-Render is disk-bound to one service and self-defeating. External S3-compatible provider required; specific provider, region and egress terms are an open decision. | **VERIFIED** (Render not viable) / **NOT VERIFIED** (provider choice) |
| 8 | Live data volume and migration scope? | **Local, measured read-only:** `projects.db` 177 MB file, 76.9 MB live blobs, 114 rows; `exports/` 1.9 GB across 838 package directories. **73 of 114 rows (64%) embed base64 PDFs in `projects.data`**; largest row **~56 MB** (`pdf_bytes` 53.1 MB + `cover_design` 2.9 MB); still written as recently as 2026-09-11; decoded at `services/packaging.py:533`. **Production volume unreadable from the development environment.** | **BLOCKER** (local verified; production **NOT VERIFIED**) |

### Environment and filesystem assumptions that break on a service split

25 environment variables are referenced in production code. Split-critical:

- `FACTORY_DB_PATH`, `FACTORY_EXPORTS_DIR`, `FLASK_EXPORTS_DIR` —
  filesystem-bound; replaced by Postgres + object storage.
- Provider keys (`AI_INTEGRATIONS_OPENAI_API_KEY`, `OPENAI_API_KEY`,
  `PEXELS_API_KEY`, `TAVILY_API_KEY`, `FACTORY_AI_POLICY`) — must be
  present on **both** services.
- `PORT`, `FACTORY_INVITE_CODE` — web-only.
- `USERPROFILE` — Windows-only; must never be required on Render.
- Fonts are materialised at runtime into `services/fonts/`
  (`services/ebook_fonts.py:101`), so each service materialises its own —
  a startup health-check item (§12), not shared state.

### Remaining unknowns (all dashboard-only or open decisions)

1. Render start command, Gunicorn `--timeout`, worker count.
2. Exact price of a `1c-2g` background worker.
3. Exact Render Postgres tier prices, connection limits, included storage.
4. Object-storage provider, region and egress terms (a decision to make).
5. Production data volume — DB size, row count, `exports/` size.

None of these change the architecture. Items 2–5 must be resolved before
the cost commitment and before migration scheduling.

## 27. Pin Factory Pro — future distribution layer

**DESIGN NOW — IMPLEMENT AFTER THE CORE FACTORY IS PRODUCTION-STABLE.**

Do not migrate, merge, or implement Pin Factory Pro during Upgrade 0. Do
not change Pin Factory Pro code. Do not change Pinterest configuration.
Do not start Pinterest approval work. Do not add infrastructure solely
for Pin Factory Pro during Upgrade 0.

Target flow:

```
PRODUCT COMPLETE / APPROVED → MARKETING JOB → PIN FACTORY PRO → PINTEREST
```

The new architecture makes this *cleaner*, not harder:

- **It is just another job type.** `CREATE_MARKETING_ASSETS` /
  `SEND_TO_PIN_FACTORY` are rows in the same `jobs` table, enqueued only
  when the product's job is `SUCCEEDED` and the artifact is APPROVED.
  Same claim, lease, retry, idempotency and observability.
- **It consumes shared storage.** It reads `assets WHERE approved = TRUE`
  by `storage_key` — which is exactly why binary extraction (§8.1b)
  benefits it directly: approved artifacts become addressable objects
  rather than base64 buried in a project row.
- **Failure isolation is structural, not promised.** Because a marketing
  job can only be *enqueued* after COMPLETE/APPROVED, a Pinterest or Pin
  Factory failure cannot prevent **product completion**, **product
  approval**, **product download**, or **PDF/ZIP export** — those events
  have already happened, on a different job, in a different failure
  domain. It additionally must never invalidate the finished product,
  force regeneration, or alter the approved PDF or cover.
- **Separate credentials, separate failure domain** (§11).
- **Idempotent** via `jobs.idempotency_key` + `work_units` — a reclaimed
  marketing job cannot create duplicate Pinterest posts.
- **Customer-facing later, operationally separate always.**
- **Same hook serves Etsy, KDP marketing and other channels.** No
  channel-specific design now.

---

## What happens to v1.7.10 (bounded chapter execution)

**Preserved and promoted, not replaced.** Its principle —
ONE BOUNDED UNIT → CHECKPOINT → NEXT UNIT — becomes `work_units`, the
core of the worker loop (§7, §9). What changes is only *who drives it*:
the worker, not the browser. The per-request chapter cap remains in force,
unchanged, until worker execution is proven by the three-live-build gate.

## ONE recommended next step

Read the five remaining unknowns (§26) off the Render dashboard — worker
and Postgres prices, connection limits, production data volume — and
decide the object-storage provider, so the cost commitment and migration
schedule rest on figures rather than estimates.
