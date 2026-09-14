# Upgrade 0 — Production Architecture Blueprint

Version 2 — revised 2026-09-14 after the owner rejected the in-process
scheduler proposal. Documentation only. No code, dependency, Render, or
database change is authorised by this document.

---

## 1. Executive summary

The Factory's product engines are good. Its execution plumbing is not.
Between v1.7.6 and v1.7.10, four separate production defects surfaced in
the ebook build, each invisible to a 2,800-test green gate, each fixed,
each followed by a new one. They were not four unrelated bugs. They were
four symptoms of one root condition: **multi-minute product generation
runs inside a synchronous HTTP request, in the same process that serves
customers, against a single JSON blob with no concurrency control.**

Upgrade 0 replaces that execution model and nothing else:

> **KEEP THE PRODUCTS. REPLACE THE PLUMBING.**

Target: the customer's browser starts a job and may close. A separate
background worker owns execution, claims work atomically from a durable
Postgres job table, checkpoints every bounded unit, survives its own
death and every deploy, and writes customer assets to shared storage the
web service can serve. Product engines, QA, renderers, covers, puzzles,
planners, packaging, Function Lock, Command Center and the test suite are
preserved as-is.

Scope discipline: Upgrade 0 changes **how work is executed**, never
**what a product is supposed to be**.

---

## 2. Current architecture (as verified in code, 2026-09-14)

| Layer | Today |
|---|---|
| Web | Flask 3.1.1, Gunicorn on Render (start command is dashboard-only; **not in this repo**, timeout/worker count unconfirmed) |
| Execution | Synchronous, inside the web request. `advance_build()` runs one stage per `/ebook/build/<id>/advance` POST |
| Trigger | The customer's **browser** drives the loop (`_ebookBuildLoop` in `static/js/app.js`) |
| State | SQLite (WAL), one table: `projects(id, name, type, data TEXT, user_saved, system_test, temporary, created_at, updated_at)` |
| Project state | The **entire** workspace — rail, chapters, ledger, QA findings, build state — is one JSON blob in `projects.data` |
| Writes | `database.update_project(pid, None, data)` **replaces the whole blob**; no version, no compare-and-swap |
| Files | 30+ modules write directly to local `EXPORTS_DIR`; Flask serves downloads with `send_from_directory` off the same disk |
| Idempotency | Per-workspace dict inside the blob: `ebook_workspace.paid_call_ledger.idempotency_keys` |
| Queue/worker | **None.** `requirements.txt` contains no Celery, RQ, APScheduler, or Redis |
| Providers | `services/ai_providers.py` — opt-in local Ollama, fail-closed to cloud (v1.7.8) |
| Protection | Function Lock registry: 4 LOCKED, 6 PROTECTED functions; Fast + Full gates |

## 3. Root architectural problems

1. **Long work inside a request.** A book takes minutes; a web request
   may not. Gunicorn kills the worker mid-write (`handle_abort` →
   `sys.exit(1)`), which is exactly what the live log showed.
2. **The browser is the scheduler.** Close the tab and the build stops.
   Execution ownership sits in the least reliable component in the system.
3. **Whole-blob read-modify-write.** `update_project` replaces all state.
   A stale in-memory copy silently erases newer work — this *already*
   caused v1.7.9's data loss **with only one writer.** It becomes a
   structural lost-update hazard the moment a worker writes concurrently.
4. **Web and generation are operationally coupled.** A deploy, restart,
   OOM or traffic spike takes generation with it.
5. **Private local disk as the asset store.** Any process that does not
   share that disk cannot produce or serve customer files.
6. **Failure state is implicit.** Retry/attempt/lease/error semantics are
   spread across an ad-hoc dict rather than a typed, queryable model.
7. **No production observability.** Diagnosis this sprint depended on the
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
| SQLite in **production** | PostgreSQL (SQLite stays valid for tests) |
| Direct `EXPORTS_DIR` filesystem coupling | Storage abstraction over shared object storage |
| Implicit attempts/ceiling in `ebook_build` dict | `jobs` table: status, attempt, lease, next_retry_at |
| Ad-hoc `log.error` only | Structured job events + queryable history |

Deprecated but **retained**: the `/advance` endpoint stays as an
idempotent manual nudge and fallback. It is never the primary driver again.

## 6. Proposed target architecture

```
CUSTOMER (browser — may close at any time)
   │  POST /ebook/build           → returns {project_id, job_id}
   │  GET  /ebook/build/<id>/status  (read-only, fast, no work)
   ▼
FLASK WEB SERVICE  ── invite gate, projects, enqueue, status,
   │                  preview, approve, download.  NO generation.
   ▼
POSTGRESQL (durable shared state)
   │   projects · jobs · work_units · job_events · assets
   ▼
JOB MANAGER  (thin module: enqueue / claim / heartbeat / complete / fail)
   │   atomic claim via SELECT … FOR UPDATE SKIP LOCKED + lease
   ▼
BACKGROUND WORKER (separate Render service, N=1 to start)
   │   loop: claim → run ONE bounded unit → checkpoint → heartbeat → repeat
   ▼
EXISTING PRODUCT ENGINES / AI PROVIDERS      ← unchanged
   ▼
PRODUCT-SPECIFIC QA (Upgrade 1 authorities)  ← unchanged
   ▼
SHARED OBJECT STORAGE  (covers, images, PDFs, ZIPs, previews)
   │   DB stores keys + metadata; storage holds bytes
   ▼
CUSTOMER DOWNLOAD  ·  (future) PIN FACTORY PRO
```

The web service and the worker share **only** Postgres and object
storage. Neither can kill the other.

## 7. Durable job-state model

Two levels, deliberately:

**Job** — one customer-visible piece of work (`BUILD_EBOOK`). Owns
status, attempts, lease, retry schedule, customer-safe message.

**Work unit** — one bounded, individually-idempotent step inside a job
(`stage:manuscript:chapter:7`). This is v1.7.10's concept, promoted to a
first-class, durable row.

Job status machine:

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
unit. Deploys are the same event as a crash, and are handled identically.

## 8. Persistence model

### 8.1 The critical finding

`projects.data` holds all state, and `update_project()` replaces it
wholesale. **Introducing a second writer without fixing this would
manufacture data loss.** Two acceptable disciplines:

- **Optimistic concurrency (recommended for Phase 1).** Add
  `projects.version INTEGER`. Every write is
  `UPDATE … SET data=?, version=version+1 WHERE id=? AND version=?`.
  Zero rows updated ⇒ someone else wrote ⇒ re-read, re-apply, retry.
  Small, mechanical, and it also closes the *existing* single-writer
  hazard.
- **Write narrowing (Phase 2).** Move volatile job/stage state out of the
  blob into typed `jobs`/`work_units` rows, so the worker rarely writes
  the blob at all and the web service owns customer-edit writes.

### 8.2 Recommended schema (Postgres)

```sql
-- EXISTING, minimally extended -------------------------------------
ALTER TABLE projects ADD COLUMN version BIGINT NOT NULL DEFAULT 0;

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
  provider              TEXT,                     -- provider used for the last unit
  idempotency_key       TEXT   NOT NULL,          -- job-level dedupe
  claimed_by            TEXT,                     -- worker instance id
  lease_expires_at      TIMESTAMPTZ,
  heartbeat_at          TIMESTAMPTZ,
  available_at          TIMESTAMPTZ NOT NULL DEFAULT now(),  -- = next_retry_at when backing off
  started_at            TIMESTAMPTZ,
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at          TIMESTAMPTZ,
  error_code            TEXT,                     -- 'PROVIDER_UNAVAILABLE', 'QA_BLOCKED', …
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
  result_ref     JSONB NOT NULL DEFAULT '{}'::jsonb,  -- asset keys / digests, not blobs
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
approved assets, by project, by kind, by key.

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
- **One bounded unit per loop turn** — v1.7.10's rule, preserved and moved
  into the worker.
- **Checkpoint before anything else.** A unit's result is durable before
  the loop advances.
- **Graceful shutdown** on SIGTERM: finish the current unit, release the
  lease, exit. Render's deploy signal becomes a clean handoff, not a loss.
- **Never mutate an approved artifact.**
- **Worker concurrency starts at 1.** `SKIP LOCKED` makes N>1 correct
  whenever it is needed, without redesign.

## 10. Durable queue / backend choice

**Recommendation: PostgreSQL as the queue. No Redis, no Celery, not yet.**

Atomic claim:

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

Why this is sufficient here: Factory volume is low (single-digit
concurrent builds), jobs are minutes long — so per-job queue overhead is
irrelevant — and `FOR UPDATE SKIP LOCKED` is a mature, well-understood
Postgres primitive. Adding Redis + Celery now would add two runtime
dependencies, a broker to operate, and a second source of truth that can
disagree with the database, in exchange for throughput the Factory does
not need.

**Adopt Redis/RQ/Celery only when a concrete trigger is hit:**
sustained queue depth that one or two workers cannot drain; a need for
sub-second dispatch latency; fan-out/chord workflows; scheduled/recurring
jobs beyond a simple sweeper; or job rates high enough that queue polling
measurably loads Postgres. None are true today. The job-manager module is
a thin interface precisely so that swap stays possible later.

## 11. Provider / configuration design

Keep v1.7.8's hard-won rule and generalise it:

- **Fail closed.** Missing/unknown configuration selects the safe cloud
  provider, never a local one. Local generation is explicit opt-in
  (`FACTORY_AI_POLICY=local_first|local_only`), and remains a local-only
  option (Ollama).
- **Never infer the environment.** No platform-detection heuristics. Two
  independent attempts to do that failed in production this sprint.
- **Per-domain credentials, per-domain failure.** Product generation,
  Pinterest/Pin Factory, and each future channel hold separate
  credentials and share no client or failure mode.
- **The worker is a configuration consumer, not a special case.** Web and
  worker read one config module; a startup health check (§12) makes a
  misconfigured worker refuse to start rather than fail per job.

## 12. Startup health validation

Both processes validate before accepting work, and log one structured
readiness line:

| Check | Web | Worker | On failure |
|---|---|---|---|
| Postgres reachable, migrations current | ✔ | ✔ | refuse to start |
| Object storage reachable, write+read+delete probe | ✔ | ✔ | refuse to start |
| Cloud AI provider key present and non-placeholder | ✔ | ✔ | refuse to start |
| `FACTORY_AI_POLICY` resolves to an explicit, valid value | ✔ | ✔ | log resolved value; local-only ⇒ refuse in production |
| Fonts/renderer assets present | — | ✔ | refuse to start |
| Disk/tmp writable | ✔ | ✔ | refuse to start |

A worker that cannot do its job must fail loudly at boot, not silently
per job — the failure mode that cost this sprint four rounds.

## 13. Error / recovery model

| Class | Example | Handling |
|---|---|---|
| Transient | provider 5xx/timeout, network reset | retry, exponential backoff + jitter, attempt+1 |
| Capacity | rate limit, budget ceiling near | longer backoff; `BLOCKED` if the budget is genuinely exhausted |
| Content/QA | manuscript fails structural QA | existing `execute_correct_manuscript`, re-QA, then approve or `BLOCKED` |
| Configuration | missing key, bad policy | `FAILED_FINAL` fast, loud; not retried into a wall |
| Poison | same unit fails deterministically at max attempts | `FAILED_FINAL`; prior completed units retained |
| Infrastructure | worker killed, deploy | lease expiry → automatic reclaim → resume |

Invariants, all of which were violated at least once this sprint:
1. Recording a failure may only **add** information — never overwrite
   newer state (v1.7.9).
2. A completed work unit is never re-executed or re-billed (v1.7.10).
3. The customer sees only `customer_safe_message`; `internal_error_detail`
   never reaches the UI.
4. A recoverable failure never becomes a customer-facing dead end (v1.7.6).

## 14. Logging / observability model

- **Structured JSON logs**, every line carrying `job_id`, `project_id`,
  `stage`, `attempt`, `worker_id`.
- **`job_events`** as the durable, queryable narrative of every job —
  diagnosis stops depending on scrollback screenshots.
- **Command Center panel** (reuses the existing app): active jobs, stage,
  attempt, lease age, last error code, oldest queued job, failed-final in
  24h, spend per job.
- **Heartbeat/lease age** is the single best liveness signal: a stalled
  worker is visible as a growing lease age before customers notice.
- **Secrets never logged.** Error detail is stored, not echoed.

## 15. Render production topology

```
┌──────────────────────┐        ┌──────────────────────────┐
│  Web Service         │        │  Background Worker       │
│  Flask + Gunicorn    │        │  python -m worker        │
│  customer traffic    │        │  generation · QA · export│
│  NO generation       │        │  concurrency 1 → N       │
└─────────┬────────────┘        └───────────┬──────────────┘
          │        both read/write          │
          ├─────────────┬───────────────────┤
          ▼             ▼                   ▼
   ┌─────────────────────────┐   ┌────────────────────────┐
   │ Render PostgreSQL       │   │ Object storage (S3-API)│
   │ projects · jobs         │   │ covers · images · PDFs │
   │ work_units · job_events │   │ ZIPs · previews        │
   │ assets (metadata)       │   │ (bytes)                │
   └─────────────────────────┘   └────────────────────────┘
```

- Web serves downloads by streaming from object storage (or a
  short-lived signed URL) instead of `send_from_directory`.
- The existing persistent disk is no longer the system of record; it may
  remain as a scratch/cache area only.
- Deploys restart both services independently; in-flight jobs survive via
  lease expiry + resume.

**Must be verified before implementation** (see §26): whether a Render
persistent disk can be attached to two services simultaneously. My
understanding is that it cannot, which is precisely why shared object
storage is required — but this project has already been bitten twice by
unverified platform assumptions, so it gets checked, not assumed.

## 16. Windows local development topology

Same shape, one machine, so local development cannot hide production
defects:

```
Launcher (one .bat)
 ├─ process 1: Flask web       (port 5055 owner / 5077 Claude)
 └─ process 2: python -m worker   ← same worker code as production
        ▼                ▼
   PostgreSQL (local)   local object-storage emulation or a local
                        filesystem storage driver behind the same interface
```

**Recommendation: run PostgreSQL locally too.** The reason is specific,
not aesthetic: `FOR UPDATE SKIP LOCKED` does not exist in SQLite, so a
SQLite local path would need a *different* claim implementation — the
exact "local hides production defects" trap the owner asked about. Same
engine both sides keeps job semantics identical.

- SQLite **remains** the engine for the test suite (fast, isolated,
  no service dependency) — tests inject a fake/stub job store or use a
  single-threaded claim shim, and a dedicated contract test asserts both
  implementations obey the same claim/lease semantics.
- Ollama stays an explicit local-only provider option, unchanged.
- If installing Postgres locally is genuinely unacceptable, the fallback
  is SQLite + a single-worker advisory-lock shim, documented as a known
  divergence with the claim path excluded from local proof. This is
  second-best and should be a deliberate choice, not a default.

## 17. Ebook pilot migration

Ebook is the only multi-minute build and therefore the only pilot.

1. **Preserve the current path.** v1.7.10 stays live and untouched while
   the new path is built behind `FACTORY_EXECUTION_MODE=legacy|worker`.
2. **Enqueue instead of execute.** `POST /ebook/build` creates the project
   *and* a `jobs` row, then returns immediately. In `legacy` mode the
   browser loop still drives; in `worker` mode it becomes read-only polling.
3. **Map stages to work units.** Existing `STAGES` become job stages;
   manuscript chapters become `work_units` (v1.7.10's bound, promoted).
   `stage_is_validated()` remains the authority on completion — the worker
   asks the same question the orchestrator asks today.
4. **Adopt storage keys.** Ebook's asset writes move behind the storage
   interface; `assets` rows record what exists.
5. **Cut over, one customer path, behind the flag.**

## 18. Migration plan for remaining products

Word Search, Crossword, Coloring Book, Math Worksheet, Spelling
Worksheet and Planners are fast, single-request generations with **no
observed timeout failures**. They are not migrated for purity.

They must, however, become compatible with the shared rules:
- provider/config module (§11) — likely already true;
- storage interface instead of direct `EXPORTS_DIR` writes;
- optimistic-concurrency writes to `projects`.

Any product that later grows a multi-minute path (multi-format export,
Flipbook, bulk generation) adopts the job/worker model at that point —
the hook exists, the work is not done speculatively.

## 19. Testing and production-release gates

Preserved: Fast Stability Gate, Full Release Gate, acceptance manifest,
`PROTECTED_GENERATOR_RULE.md` discipline, customer-path proof.

Added for Upgrade 0:
- **Job-contract tests** — claim is atomic under concurrency; an expired
  lease is reclaimed exactly once; a completed unit is never re-run;
  retry backoff respects `max_attempts`.
- **Crash-recovery tests** — kill a worker mid-unit; assert resume from
  checkpoint with no duplicate billable call.
- **Deploy-simulation test** — SIGTERM mid-job; assert clean release and
  resume.
- **Lost-update test** — concurrent web + worker writes; assert optimistic
  concurrency rejects the stale write instead of erasing data.
- **Browser-close test** — start a job, drop the client, assert completion.
- **Storage-driver contract test** — local and object-storage drivers
  behave identically.
- **No new flaky timing tests.** The worker loop exposes an injectable
  single `tick()` for tests; the suite never sleeps on real threads.

Unchanged rule, reinforced by this sprint: **a green gate is necessary,
never sufficient.** Live proof closes a production defect.

## 20. Function Lock 2.0 implications

Function Lock is preserved. Upgrade 0 changes execution, so the registry
must describe execution:

1. **New shared dependencies to declare** — `services/jobs/*`,
   `services/storage/*`, the worker entrypoint, and (if touched) `app.py`
   and `database.py`. `invite_protection` (LOCKED) declares all of
   `app.py`, so enqueue-endpoint edits require its unlock/relock cycle —
   the same ceremony already used four times this sprint.
2. **Execution-mode dimension.** A function proven under `legacy` is not
   automatically proven under `worker`. Add an execution-mode field to a
   function's lock record; a LOCKED function's proof names the mode it
   was proven in.
3. **Re-lock requires live proof.** For Upgrade 0, "protected tests green"
   is not enough to re-lock ebook — the three-live-build gate (§18/0D) is
   the proof.
4. **No bulk unlocking.** Each affected function unlocks, changes,
   re-proves and re-locks individually.

## 21. Cost implications

**Required for production (estimates — confirm current Render pricing before committing):**

| Item | Estimate/month |
|---|---|
| Background Worker service (sized like today's web instance) | ~$7 |
| Managed PostgreSQL (smallest paid tier with a real backup story) | ~$6–19 |
| Object storage at Factory volume (single-digit GB, e.g. Cloudflare R2/B2) | ~$0–2 |
| **Total additional** | **≈ $13–28** |

Unchanged: the existing web service (~$7). The persistent disk may be
reduced or dropped once storage moves, partially offsetting the above.

**Optional future scaling (not now):** additional workers (~$7 each),
larger Postgres tier, Redis/queue broker if §10's triggers are ever hit,
CDN for downloads.

The honest framing the owner asked for: this is roughly the price of one
coffee a week to stop shipping a product line whose builds die mid-run.
It is also not a licence to over-provision — one worker, the smallest
credible Postgres, and usage-priced storage is the whole recommendation.

## 22. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | **Lost updates** from whole-blob writes with two writers | **High** | Optimistic concurrency (§8.1) lands *before* the worker writes anything; dedicated test |
| 2 | **Storage migration blast radius** — 30+ modules write `EXPORTS_DIR` | **High** | Storage *interface* preserving current call semantics; migrate ebook first; other products unchanged until touched |
| 3 | Unverified Render platform facts (disk sharing, timeout, worker count) | High | §26 verification list completed before any build work |
| 4 | SQLite → Postgres data migration of live customer projects | High | Side-by-side, read-only export/verify/import, no destructive cutover; legacy path stays until proof |
| 5 | Two deployables drift out of sync (web vs worker code versions) | Medium | Same repo, same image, deploy together; version stamped in readiness log and job rows |
| 6 | Duplicate paid generation during reclaim | Medium | `work_units` unique key is the guarantee; test asserts no re-billing |
| 7 | Long-running unit exceeds the lease and is stolen mid-work | Medium | Heartbeat renews the lease; lease ≫ p99 unit duration; fencing via `claimed_by` check on write |
| 8 | Scope creep — "redesign everything" | Medium | §4 preserve-list is binding; ebook-only pilot |
| 9 | Postgres becomes a single point of failure | Medium | Managed service with backups; health check; the failure is loud, not silent |
| 10 | Cost creep from idle worker | Low | Start at one worker; revisit only on §10 triggers |

## 23. Rollback strategy

Rollback is a **configuration change, not a code revert**, at every phase:

- `FACTORY_EXECUTION_MODE=legacy` restores the proven v1.7.10 path
  instantly. The legacy path is never deleted during migration.
- The `/advance` endpoint is retained permanently as an idempotent nudge.
- Postgres migration is **additive-only** (new tables; `projects.version`
  defaults to 0). No destructive migration in Phase 1.
- Storage: assets are written to object storage **and** readable from the
  legacy path during transition; the download route falls back.
- Worker rollback = scale the worker service to zero; the web service is
  unaffected.
- A tagged release + verified DB backup precedes every phase cutover.

## 24. Estimated implementation phases

| Phase | Content | Exit criterion |
|---|---|---|
| **0A** | This blueprint, approved | Owner approval |
| **0B-1** | Platform verification (§26) | Every assumption confirmed or corrected |
| **0B-2** | Postgres + schema + `projects.version` optimistic concurrency, dual-write/read-verify; **no worker yet** | Lost-update test green; live app unchanged on Postgres |
| **0B-3** | Storage interface + object storage driver; ebook asset writes behind it | Storage contract test green; downloads identical |
| **0B-4** | Job manager + worker skeleton behind `FACTORY_EXECUTION_MODE`, off by default | Claim/lease/retry/crash tests green |
| **0C** | Ebook migrated to worker execution | Full Gate green; flag-on in production |
| **0D** | **Three successful live ebook builds in a row**, different subjects, covering manuscript, checkpointing, correction, visuals, cover, design, QA, export, and browser-close/reopen | 3/3, no code change between |
| **0E** | Remaining long-running workflows; other products adopt config/storage/concurrency rules only | Per-product proof |

## 25. Recommended technology choices

| Concern | Choice | Why |
|---|---|---|
| Database | **PostgreSQL** (Render managed) | `SKIP LOCKED`, real transactions, real concurrency |
| DB driver | `psycopg` (v3) | Current, well-supported |
| Schema changes | Plain SQL migration files, applied at boot, checked by health check | Small, auditable, no ORM adoption |
| ORM | **None.** Keep the existing thin DAL style | `database.py` is already hand-rolled; adding SQLAlchemy is scope creep |
| Queue | **Postgres job table** (§10) | Sufficient, one fewer moving part |
| Worker | Plain Python process, same repo | No framework needed for one loop |
| Object storage | **S3-compatible** (Cloudflare R2 or Backblaze B2), `boto3` | Standard API, cheap at this volume, portable |
| Local DB | PostgreSQL (same engine) | Keeps job semantics identical (§16) |
| Test DB | SQLite + claim shim, plus a contract test | Keeps the suite fast and hermetic |
| Logging | stdlib `logging` + JSON formatter | No new dependency |
| Scheduling/sweeper | Worker's own loop | No APScheduler/cron needed |

Rejected for now, with the trigger that would change the answer:
Celery/RQ (§10 triggers), Redis (same), Kubernetes/containers (not until
Render is outgrown), SQLAlchemy (only if the DAL becomes unmanageable).

## 26. Assumptions that must be verified before implementation

This project has lost two production cycles to confidently-held,
unverified platform assumptions. Nothing below may be treated as fact
until checked:

1. Whether a Render persistent disk can attach to two services at once
   (drives the necessity of object storage).
2. The **actual** Render start command, Gunicorn `--timeout` and worker
   count (still unknown; dashboard-only).
3. Render Background Worker availability and price on the current plan.
4. Render PostgreSQL tiers, price, backup policy, connection limits.
5. Current instance size (CPU/RAM) and whether one worker fits beside it.
6. Whether the web service is single- or multi-instance today.
7. Object-storage provider choice, region, egress terms.
8. Live production data volume to migrate (project count, DB size,
   `exports/` size).

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
  Same claim, lease, retry, idempotency and observability — no second
  execution system.
- **It consumes shared storage.** It reads `assets WHERE approved = TRUE`
  by `storage_key`. It never regenerates anything and never writes to the
  product's approved assets.
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
- **Customer-facing later, operationally separate always.** It may appear
  as a "Promote this product" module inside the Factory UI while running
  as its own service behind the same job/asset boundary.
- **Same hook serves Etsy, KDP marketing and other channels.** No
  channel-specific design now — the hook is the completed-product asset
  set plus a gated job type.

---

## What happens to v1.7.10 (bounded chapter execution)

**Preserved and promoted, not replaced.** Its principle —
ONE BOUNDED UNIT → CHECKPOINT → NEXT UNIT — becomes `work_units`, the
core of the worker loop (§7, §9). What changes is only *who drives it*:
the worker, not the browser. The per-request chapter cap remains in force,
unchanged, until worker execution is proven by the three-live-build gate.

## ONE recommended next step

Complete §26's verification list — the eight platform and data facts —
and record the answers in this document, before any implementation.
