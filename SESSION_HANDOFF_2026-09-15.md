# Session handoff — 2026-09-15

## Start here

Read `AUTONOMOUS_UPGRADE_STANDING_ORDERS.md` first, then this file.

**The next genuinely unfinished step is the PRODUCTION embedded-PDF
migration, run from the Render Shell.** It is waiting on one typed
command. Everything before it is done.

```
python pmig.py
```

Typed in Render → Factory web service → Shell, from `~/project/src$`.
No arguments means inventory only: it reads, prints a summary, writes
nothing, and contacts no provider.

---

## Ground truth (verified 2026-09-15, not copied forward)

| | |
|---|---|
| HEAD | `692e17d` |
| `main` == `origin/main` | yes |
| Working tree | clean |
| VERSION | **1.7.16** |
| Full Windows release gate | 3,012 tests · 0 failures · 0 errors · 0 skipped · 0 paid API calls |

**A handoff dated 2026-09-15 circulated describing HEAD `736e429`,
VERSION 1.7.14, and "67 embedded PDFs remaining". That document was
written from a state several commits behind reality and is superseded by
this one.** The bulk migration it lists as the next step was completed.

### Local database — embedded PDFs fully migrated

| | |
|---|---|
| Projects | 114 |
| Rows retaining `pdf_bytes` | **73** (none removed) |
| Asset rows | **73** |
| R2 customer objects | **73** (51,727,628 bytes) |
| Migrated / remaining | **73 / 0** |
| Project data blobs changed | 0 |
| Project versions bumped | 0 |
| Exports | 3,224 files / 1,944,650,540 bytes — unchanged |

### Production — NOT migrated

Production runs on a Render persistent disk with **its own separate
SQLite database**. The local migration proves nothing about production.
Production has **zero asset rows**, so enabling R2 reads there today
would be a verified no-op: `list_assets_exist()` returns False and R2 is
never contacted.

| | |
|---|---|
| R2 variables on Render | **configured** (owner added them 2026-09-14) |
| `FACTORY_STORAGE_DRIVER` on Render | **unset** — deliberately |
| Production PDFs migrated | **0** |
| Postgres / Background Worker | not created |

---

## What was completed since the superseded handoff

**Phase 0B-3B2D — bulk migration (local), no code change, VERSION stayed 1.7.14.**
All 67 remaining PDFs migrated in batches A–E (327 alone first at 41.76 MB,
then 20/20/20/6), each batch with its own verified backup, per-project
checksum verification, idempotency re-run, and a re-verified sample of
earlier assets. Total 51,727,628 bytes — exactly the original dry-run
prediction. Seven `PRE-0B3B2D-*` backups are in `Factory Control Center\Backups\`.

Two pre-existing conditions surfaced and proven unrelated to storage:
project 327's export is blocked by the Coloring Book QA gate, and
projects 291/323/308 trigger the crossword full-book rebuild. Both behave
identically with the driver unset.

**Phase 0B-3E — production migration mechanism.**
- `v1.7.15` (`3b28b65`, relock `ee7afc6`): `services/storage/production_migration.py`
  (inventory / backup / bounded migrate / verify, reusing the proven
  executor) plus a token-gated `POST /admin/storage-migration`, added when
  Render Shell was believed unavailable.
- `v1.7.16` (`692e17d`): `pmig.py`, a typed CLI, after Shell turned out to
  be available and its window was found to mangle pasted multi-line input.

Bug caught during that work: `migrate()` was consuming `inventory()`'s
200-row display cap, so a production database with more eligible projects
would have left the tail silently unmigrated. Fixed, with a test pinning it.

---

## Cleanup owed once production migration completes

`pmig.py` and the `/admin/storage-migration` route both exist only to
reach production. Remove them together afterwards — including the
`invite_protection` exemption the route added. The route is inert
meanwhile: it returns 404 unless `FACTORY_MIGRATION_TOKEN` is set on the
host, and it is not set.

## Owner decision pending

After the production migration verifies, the next owner-level decision is
whether to enable R2 reads in production (`FACTORY_STORAGE_DRIVER=r2`) or
move to 0B-4 (Postgres). **Do not remove any `pdf_bytes` either way.**
