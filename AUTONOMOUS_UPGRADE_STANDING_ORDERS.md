# Autonomous Safe-Upgrade Standing Orders

Established 2026-09-15 at the owner's request. Binding on every session
until the owner replaces or withdraws it.

The owner does not want to approve every routine technical checkpoint
inside an already-approved phase. Continue automatically through safe
work; stop only at a genuine owner decision or a safety boundary.

---

## The one rule that overrides everything else

**The repository and the live database are the authority — not a prompt,
and not a handoff document.**

Verify state before acting: `git log`, `VERSION`, the newest handoff,
`command_center/handoff_status.json`, `command_center/roadmap.json`, the
blueprint, and the live `projects.db` / `assets` state.

Prompts have been repeated by accident more than once, and a handoff has
been written from a state several commits behind reality. **Do not re-run
a phase merely because a prompt or a document describes it as pending.**
If a document disagrees with the repository, the repository wins — say
so plainly, then continue from the first genuinely unfinished step.

---

## Continue automatically (do NOT ask)

Inside an already-approved phase:

- audit, inspect, dry-run, plan
- back up (a backup is always safe; an unverified backup is not — prove
  the checksum)
- migrate using COPY → VERIFY → RECORD → READ BACK → VERIFY → KEEP LEGACY
- run targeted suites, the Fast Stability Gate, the Full Windows gate
- fix defects introduced within the current scope
- unlock → test → relock a Function Lock, following the procedure exactly
- bump `VERSION` when production code changes, and write the CHANGELOG entry
- update the handoff and Command Center records
- commit and push
- continue to the next approved internal checkpoint

Never ask "would you like me to continue?" inside approved scope.

## Stop and ask (ALWAYS)

- deleting `pdf_bytes`, legacy customer files, or any legacy artifact
- any irreversible or destructive operation
- changing Render production configuration or production secrets
- production database cutover, or enabling R2 reads in production
- creating or purchasing a paid Render service (Postgres, Background Worker)
- billing or DNS changes
- a material architecture change
- anything needing a credential only the owner holds
- a security issue
- **an unexplained data or checksum mismatch** — stop on the first one
- a required release gate that cannot be fixed safely
- any marketing implementation

When stopping for a manual step, give **one step at a time**: exactly
where to click, exactly what to type. No long prompts to paste back.

---

## Safety principles that must not be lost

**Legacy is the rollback path.** Keep `pdf_bytes`, export files, the
legacy read fallback, and the legacy execution mode until the replacement
has been live and proven for a real period. "Migrated" never means
"legacy removed".

- An R2 failure must never break a valid legacy customer product.
- A marketing failure must never break a completed product.
- No paid provider calls during infrastructure work.
- No unnecessary product generation.
- Never weaken a test to get a green gate. If a gate catches something,
  it was right — fix the cause.
- Report outcomes faithfully: if a gate fails, say so with the output; if
  a step was skipped, say that.

---

## Where the work actually stands

Verify this against the repository rather than trusting it. As of
2026-09-15, Upgrade 0's next genuine step is the **production** embedded-PDF
migration: the local database is fully migrated, but production runs on a
Render persistent disk with its own separate SQLite file, so local
migration proves nothing about production. See the newest handoff.

Roadmap order: 0B-3 storage → 0B-4 Postgres → 0B-5 job manager + worker →
0C ebook worker migration → 0D three live ebook builds → 0E remaining
workflows. Marketing (MARKETING-1 … 6) only after production stability.
