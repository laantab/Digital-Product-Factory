# Session Handoff — 2026-08-31 (supersedes 2026-08-29)

**Start a new session with:** "Read SESSION_HANDOFF_2026-08-31.md and continue."

---

## What happened this session

### 1. The owner's PC was running an August 10 build — fixed
The folder Cursor opened (`Documents\product-pipeline\Product-Pipeline\flask_app`)
was ~39 commits behind origin/main and had no `_run_factory_5055.py`. v1.3.0 was
cloned fresh from GitHub to **`C:\Users\user\Documents\Product-Pipeline\Factory-v1.3`**
with `projects.db` and `.env` copied in. The desktop launcher **`Open Factory.bat`**
(on the OneDrive desktop — the visible one) starts THAT folder on port 5055 via
`Desktop\The Factory\run5055.py`. The old folder is untouched.

### 2. THE 2026-08-29 BLOCKER IS FIXED — the whole pre-manuscript path now runs from the UI
The blocker was bigger than run_research: research, title, AND outline all had
registered paid actions but **no executor and no UI controls**, and research had
no Approve button. A fresh workspace dead-ended at `next_action: "run_research"`.

Built (mirroring the manuscript estimate → confirm → execute pattern):

* **`services/ebook_research_engine.py` (new)** — `run_topic_research` (one
  Tavily search + one synthesis call), `generate_title_options` (3 options),
  `generate_outline_options` (6–10 chapters). FACTORY_TEST_MODE returns
  deterministic offline payloads, zero provider calls; live provider failures
  fail open to input-backed drafts. Each reports `paid_calls` actually made —
  only those are charged (offline/test = $0).
* **`services/ebook_project_workspace.py`** — `execute_run_research`,
  `execute_generate_title_options`, `execute_generate_outline_options`
  (+ shared `_consume_confirmed_simple_action` / `_charge_simple_action`),
  `RESEARCH_AUTH_MAX_USD = 0.50`, and estimate guards so run_research can't be
  re-bought while its output awaits approval. Same protections as manuscript:
  confirmation token, artifact/revision match, auth cap, budget cap,
  idempotency-key replay without extra charge.
* **`app.py`** — `POST /ebook-workspace/<id>/run-research`, `/title-options`,
  `/outline-options` (shared `_run_confirmed_workspace_action` helper).
* **`static/js/app.js`** — the "Next production action" bar now renders a real
  button for run_research / generate_title_options / generate_outline_options;
  the Research panel gained **Approve Research**; the Title and Outline panels
  gained option pickers (radio) with **Approve Title** / **Approve Outline**;
  new confirm flows `estimateResearchInWorkspace` and
  `estimateOptionGenerationInWorkspace` mirror the manuscript one.

Customer path now: create workspace → Run Research… ($0.50 max) → Approve →
Generate Title Options… ($0.15) → pick + Approve → Generate Outline Options…
($0.20) → pick + Approve → **Generate Manuscript unlocks** (existing flow).

### 3. Tests
**`tests/test_ebook_pre_manuscript_actions.py` (new, 10 tests)** — executor
unit tests (charge recorded, idempotent replay, used-token blocked, offline =
$0) plus an HTTP journey over the real routes from fresh workspace to
`manuscript_enabled: true` with $0 spent. All 10 pass. The ebook/workspace
subset (473 tests) passes. NOTE: an early subset run showed 21 failures that
were ALL environment (pip had installed pypdf 3.x; the repo pins
**pypdf==6.10.0** — with the pin restored everything passed).

## Standing open items (carried from 2026-08-29, still open)

1. Make the Cloudflare tunnel durable (Windows service) or accept ad hoc.
2. Owner must finish Lemon Squeezy's business-details form with
   `https://digitalproductfactorypro.com`.
3. Cosmetic: `".,"` collision when an AI idea name ends in a period.
4. Unify the three review-key names (`qa_report` / `qa_result` / `editor_in_chief`).
5. Retire `Update_API_Key_Anywhere.bat`.
6. Long-standing: plan limits in `/generate-product`; rotate Tavily + Pexels
   keys; real user accounts before live payments; 1.5 GB DB purge; repo visibility.
7. NEW: commit + push this session's changes to origin/main from the owner's PC
   (the cloud session cannot push). Files: app.py,
   services/ebook_project_workspace.py, services/ebook_research_engine.py,
   static/js/app.js, tests/test_ebook_pre_manuscript_actions.py, this handoff.

## Working notes

* The owner is a **novice** — plain language, one next step at a time.
* The app now runs from `Factory-v1.3`; kill-and-relaunch = double-click
  `Open Factory.bat`. Hard-refresh (Ctrl+F5) after app.js changes.
* Live research/title/outline calls spend real money ($0.50/$0.15/$0.20 max
  per confirmation). Verify UI wiring with free estimate + cancel, never by
  confirming a live run.
