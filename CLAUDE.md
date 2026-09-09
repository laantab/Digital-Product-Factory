# Digital Product Factory — start here

This folder (`C:\Users\user\Documents\Product-Pipeline\Factory-v1.3`) is the ONLY live
checkout. Every Desktop launcher runs it and GitHub tracks it
(`github.com/laantab/Digital-Product-Factory`, branch `main`). The OneDrive folder
`Factory_Stabilized_Source_V2_20260809\Factory_Stabilized_V2\flask_app` is an archived
copy: never edit or test there.

## First five minutes of every session

1. Read the newest `SESSION_HANDOFF_*.md` in this folder. It says where work stopped
   and what is open. Start from its "Start here" section.
2. Run `git status` and `git log --oneline -5`. Expect a clean tree on `main`.
3. Run the fast Stability Gate (below). Do not start new work on a RED gate.

## Running the app

- The owner's own server: `Desktop\Open Factory.bat` runs `_run_factory_5055.py` on
  port 5055. Do not kill it and do not start another server on 5055.
- Claude's server: use `.claude/launch.json` config `factory-5077` (port 5077) so it
  never collides with the owner's window.
- The app runs with `use_reloader=False`. After every code change, kill and relaunch
  the server or the change is not live. Many "the fix didn't work" moments were a
  stale process.
- Python: `C:\Users\user\AppData\Local\Python\pythoncore-3.14-64\python.exe`.

## Gates

Fast Stability Gate (about 25 seconds, zero cost), from this folder:

```
C:\Users\user\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pytest -q tests\factory_golden_customer_path_smoke_suite.py tests\test_universal_topic_puzzle_engine.py tests\test_crossword_scope_answerkey_zip_repair.py tests\test_coloring_book_sea_creatures_customer_path.py tests\test_coloring_book_local_fallback_theme_classification.py tests\test_spelling_worksheet_topic_relevance.py tests\test_spelling_worksheet_release_readiness.py tests\test_spelling_worksheet_semantic_scope.py tests\test_african_animals_topic_repair.py tests\test_customer_journey_every_product_type.py tests\test_ebook_saved_projects_visibility.py tests\test_saved_projects_reopen_build.py tests\test_reopen_packaging_identity_pass2.py tests\test_download_slug_package_id.py
```

Same thing as a double-click:
`Documents\Product-Pipeline\Factory Control Center\Launchers\RUN_FACTORY_STABILITY_GATE.bat`.

Full Windows release gate (run before any release, uses a temporary database):
`python scripts\run_factory_tests.py`. New test files must be added to
`tests\acceptance_manifest.json` or the gate will not run them.

## Rules that are not optional

- `Documents\Product-Pipeline\Factory Control Center\FACTORY_STABILITY_RULES.md` is
  binding. In short: a feature is protected only by a customer-path test, previously
  green customer behavior is never changed without explicit say-so, shared-service
  edits need the dependent products' smoke tests, and tests are never weakened to
  hide a regression.
- Never make a paid API call (OpenAI, Pexels, Tavily, image generation) without the
  owner's explicit go-ahead in that session.
- `projects.db`, `exports/`, PDFs and ZIPs are local only and gitignored.
- Bump `VERSION` and add a plain-language `CHANGELOG.md` entry with each real release.
- The repo is public. Commit at the end of a session; ask before pushing unless the
  owner has already said to push.
- The same logic is sometimes implemented twice (Python and JS). Grep for the second
  copy before calling a fix done.

## Where things live

- `Factory Control Center\Reviews\Factory Stability\` — feature stability matrix,
  shared-service dependency map, dashboard.
- `Factory Control Center\Logs\` — gate logs by date.
- `Factory Control Center\Backups\` — dated `projects.db` backups.
- `SESSION_HANDOFF_*.md` here — one per working day, newest wins.
- `*_LOCKED_STATE.md` here — behaviors that are frozen; read before touching that product.
