# Session handoff — 2026-09-15

## Start here

Read `AUTONOMOUS_UPGRADE_STANDING_ORDERS.md` first, then this file.

**Phase 0B-3 (Storage / R2) is COMPLETE, including production.** R2 reads
are live in production with legacy fallback intact.

**The next approved step is 0B-4 (PostgreSQL) — not yet started, and it
needs the owner's go-ahead because it means creating a paid Render
service.**

---

## Ground truth (verified 2026-09-15)

| | |
|---|---|
| HEAD | `471004f` |
| `main` == `origin/main` | yes |
| Working tree | clean |
| VERSION | **1.7.19** |
| Full Windows release gate | 3,028 tests · 0 failures · 0 errors · 0 skipped · 0 paid API calls |

---

## PRODUCTION — R2 reads ENABLED (milestone, 2026-09-15)

Confirmed by the owner running the verification commands on the live
Render instance. These are production-side results; this machine cannot
reach `/var/data/projects.db`.

| | |
|---|---|
| Factory version in production | **v1.7.19** |
| `FACTORY_STORAGE_DRIVER` | **`r2`** — R2 reads enabled |
| Production projects | 9 |
| Projects with `pdf_bytes` | 4 |
| Embedded PDFs migrated to R2 | **4** |
| Pending migration | **0** |
| Asset rows | **4** |
| Legacy `pdf_bytes` retained | **YES — all 4** |
| `readcheck` | **PASS** |
| Fallback verification | **PASS** |
| Live customer Saved Projects / download smoke test | **PASS** |
| Legacy data deleted | **NONE** |

**Rollback is one step and remains available:** set
`FACTORY_STORAGE_DRIVER` to `local` (or delete the variable). Reads return
to the legacy copies immediately — no data repair, no restore, no code
change. This works *only* because every legacy `pdf_bytes` is still
present. **Do not delete them.**

A successful R2 read performs **no write of any kind**: no project blob
rewrite, no version bump, no lifecycle change, no asset update. The read
path is a `SELECT` plus an R2 `head`/`get`. Audited in code before
enablement.

### Local database (separate from production)

73 of 73 embedded PDFs migrated, 73 asset rows, 73 R2 objects,
51,727,628 bytes, all 73 legacy `pdf_bytes` retained, 114 projects,
3,224 export files unchanged.

---

## Storage tooling now in the repo

| Command | What it does |
|---|---|
| `python pmig.py` | inventory — READ ONLY (the default) |
| `python pmig.py backup` | timestamped, checksum-verified copy |
| `python pmig.py migrate` | the full guarded production sequence |
| `python pmig.py migrate N` | raw bounded batch, local use |
| `python pmig.py verify` | re-verify migrated assets against legacy |
| `python pmig.py readcheck` | which source the REAL reader chooses, plus a safe fallback probe |

`migrate` is fail-closed at every gate: it refuses unless the database is
on the persistent disk, R2 is fully configured, the driver is still
unset, and no record is malformed — and it will not migrate at all unless
a backup has been proven byte-identical.

## Cleanup owed (not urgent, not yet done)

`pmig.py` and the token-gated `POST /admin/storage-migration` route
(v1.7.15) both exist only to reach production storage. Once there is no
further production migration work, remove them together, including the
`invite_protection` invite-gate exemption the route added. The route is
inert meanwhile: 404 unless `FACTORY_MIGRATION_TOKEN` is set, and it is
not set.

---

## Next step — 0B-4 PostgreSQL (OWNER DECISION REQUIRED)

Roadmap: **0B-3 storage ✅ → 0B-4 Postgres → 0B-5 job manager + worker →
0C ebook worker migration → 0D three live ebook builds → 0E remaining
workflows.** Marketing (MARKETING-1…6) only after production stability.

0B-4 is an owner stop condition: it means **creating and paying for a
Render PostgreSQL instance**, and the blueprint (§26) requires a paid tier
with backups and recovery. Do not create it without explicit approval.

Still-open items carried forward: the owner's live ebook re-test of the
v1.7.10 bounded-generation fix, and the §26 dashboard-only unknowns
(Render start command / Gunicorn timeout / worker count, worker and
Postgres pricing, connection limits).

**Do not delete any `pdf_bytes`.** Do not migrate export files. Those are
separate, later, separately-approved decisions.
