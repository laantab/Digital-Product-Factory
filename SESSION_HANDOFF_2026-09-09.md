# Session Handoff — 2026-09-09 (supersedes 2026-09-04)

**Start a new session with:** "Read CLAUDE.md and SESSION_HANDOFF_2026-09-09.md and continue."

---

## Where things stand

- `main` = `origin/main` = `e81298e`. Tree clean. Everything on this machine is on
  GitHub. VERSION `1.5.0`.
- Fast Stability Gate: GREEN (123 passed, 593 subtests) at 2026-09-09 14:00.
- Full Windows release gate: GREEN this morning per the audit session (2,451 tests,
  0 failures, 0 paid calls) after the African Animals fix.
- A source snapshot of this folder plus the Factory Control Center docs is at
  `OneDrive\Desktop\Factory_Stabilized_Source_V2_20260809\safety_snapshots\Factory-v1.3_source_2026-09-09`.

## What happened today

1. **Morning audit session** (Sonnet): Universal Topic Vocabulary engine
   (`services/factory/topic_vocabulary.py`, `data/topic_vocabulary_packs.json`) now
   feeds Crossword, Word Search and Spelling Worksheet. Added real Ocean Animals and
   African Animals categories. Fixed Crossword topic contamination and the dropped
   answer key on Single page. Released Spelling Worksheet. Fixed Coloring Book
   local-fallback theme classification. Created the Factory Stability Gate, the
   Golden Customer-Path Smoke Suite, `FACTORY_STABILITY_RULES.md`, and the stability
   matrix in the Factory Control Center.
2. **Afternoon** (Fable): committed the uncommitted v1.5.0 ebook work from Sep 6 to 8
   (`279415a`) and this morning's work (`e81298e`), pushed all 13 waiting commits.
3. **Discovered two checkouts.** The OneDrive copy had its own unpushed edits from
   Sep 1 to 3. Those are rescued, untouched, on branch `onedrive-workspace-phase-a`
   (`19fdd51`, pushed). Added `CLAUDE.md` here and a redirect `CLAUDE.md` in the
   OneDrive folder so a session opened in the wrong place is told where to go.

## Start here: open decisions for the owner

1. **Branch `onedrive-workspace-phase-a`: merge, cherry-pick, or drop?** It holds
   Ebook Project workspace Phase A (Run Research / Approve Title / Draft Outline
   controls with seeded research), the Factory Market Advantage repeated-warning fix,
   one-click full build with a progress tracker, in-progress projects reachable from
   Saved Projects, and the logo on the three standalone builder pages (untested).
   `main` solved some of the same problems differently on Sep 4 ("Add ebook
   pre-manuscript actions", "Make finished ebooks visible in Saved Projects"). Go
   feature by feature, with the gate, not by file copy. Nothing is lost either way.
2. **Which GitHub repo is real?** `Desktop\Factory Backup\BACKUP-FACTORY-TO-GITHUB.bat`
   uploads zips to `laantab/The-Digital-Product-Factory`; this checkout pushes to
   `laantab/Digital-Product-Factory`. Pick one and retire the other script.
3. **Restart the 5055 server** if it has been running since before this morning's
   vocabulary edit; it caches the vocabulary file at startup.
4. Still open from earlier handoffs: rotate Tavily and Pexels keys; real user accounts
   before live payments; enforce plan limits in `/generate-product`; make the
   Cloudflare tunnel a Windows service; sweep Farm / Rainforest / Arctic Animals
   topics for the same vocabulary gap.

## Not done today, on purpose

- No merge of the OneDrive branch (needs owner decisions above).
- No deletion or rename of the OneDrive copy. It is now redundant but harmless.
- The 1.1 GB of `projects.db` backups in the Factory Control Center were not copied
  to OneDrive.
